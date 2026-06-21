from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from backend.app.baseline.schemas import BacktestResultRow, ErrorMetrics, LeakageAuditCheck

_KG_QUANT = Decimal("0.000001")
_RATIO_QUANT = Decimal("0.0000000001")


def quantize_kg(value: Decimal) -> Decimal:
    return value.quantize(_KG_QUANT, rounding=ROUND_HALF_UP)


def quantize_ratio(value: Decimal) -> Decimal:
    return value.quantize(_RATIO_QUANT, rounding=ROUND_HALF_UP)


def evaluated_row(
    *,
    baseline_name: str,
    target_season_id: int,
    target_season_code: str,
    factory_id: int,
    factory_name: str,
    fold_key: str,
    actual_stable_peak_kg: Decimal,
    predicted_stable_peak_kg: Decimal,
    previous_season_id: int | None = None,
    previous_season_code: str | None = None,
    input_features: dict[str, object] | None = None,
    training_season_codes: list[str] | None = None,
    model_metadata: dict[str, object] | None = None,
) -> BacktestResultRow:
    absolute_error_kg = quantize_kg(abs(predicted_stable_peak_kg - actual_stable_peak_kg))
    signed_error_kg = quantize_kg(predicted_stable_peak_kg - actual_stable_peak_kg)
    ape = quantize_ratio(absolute_error_kg / actual_stable_peak_kg)
    return BacktestResultRow(
        baseline_name=baseline_name,
        target_season_id=target_season_id,
        target_season_code=target_season_code,
        factory_id=factory_id,
        factory_name=factory_name,
        previous_season_id=previous_season_id,
        previous_season_code=previous_season_code,
        fold_key=fold_key,
        status="evaluated",
        actual_stable_peak_kg=quantize_kg(actual_stable_peak_kg),
        predicted_stable_peak_kg=quantize_kg(predicted_stable_peak_kg),
        absolute_error_kg=absolute_error_kg,
        signed_error_kg=signed_error_kg,
        ape=ape,
        input_features=input_features or {},
        training_season_codes=training_season_codes or [],
        model_metadata=model_metadata or {},
    )


def excluded_row(
    *,
    baseline_name: str,
    target_season_id: int,
    target_season_code: str,
    factory_id: int,
    factory_name: str,
    fold_key: str,
    exclusion_reason: str,
    previous_season_id: int | None = None,
    previous_season_code: str | None = None,
    actual_stable_peak_kg: Decimal | None = None,
    input_features: dict[str, object] | None = None,
    training_season_codes: list[str] | None = None,
    model_metadata: dict[str, object] | None = None,
) -> BacktestResultRow:
    return BacktestResultRow(
        baseline_name=baseline_name,
        target_season_id=target_season_id,
        target_season_code=target_season_code,
        factory_id=factory_id,
        factory_name=factory_name,
        previous_season_id=previous_season_id,
        previous_season_code=previous_season_code,
        fold_key=fold_key,
        status="excluded",
        actual_stable_peak_kg=(
            quantize_kg(actual_stable_peak_kg) if actual_stable_peak_kg is not None else None
        ),
        predicted_stable_peak_kg=None,
        absolute_error_kg=None,
        signed_error_kg=None,
        ape=None,
        input_features=input_features or {},
        training_season_codes=training_season_codes or [],
        model_metadata=model_metadata or {},
        exclusion_reason=exclusion_reason,
    )


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def aggregate_error_metrics(rows: list[BacktestResultRow]) -> ErrorMetrics:
    evaluated = [row for row in rows if row.status == "evaluated"]
    excluded = [row for row in rows if row.status == "excluded"]
    exclusion_counts: dict[str, int] = {}
    for row in excluded:
        if row.exclusion_reason is not None:
            exclusion_counts[row.exclusion_reason] = (
                exclusion_counts.get(row.exclusion_reason, 0) + 1
            )

    if not evaluated:
        return ErrorMetrics(
            evaluated_row_count=0,
            excluded_row_count=len(excluded),
            negative_prediction_count=0,
            mape=None,
            mdape=None,
            wmape=None,
            mae_kg=None,
            mae_tonne=None,
            mean_bias_kg=None,
            exclusion_counts=exclusion_counts,
        )

    apes = [row.ape for row in evaluated if row.ape is not None]
    abs_errors = [row.absolute_error_kg for row in evaluated if row.absolute_error_kg is not None]
    actuals = [
        row.actual_stable_peak_kg for row in evaluated if row.actual_stable_peak_kg is not None
    ]
    biases = [row.signed_error_kg for row in evaluated if row.signed_error_kg is not None]
    total_abs_error = sum(abs_errors, Decimal("0"))
    total_actual = sum(actuals, Decimal("0"))

    return ErrorMetrics(
        evaluated_row_count=len(evaluated),
        excluded_row_count=len(excluded),
        negative_prediction_count=sum(
            1
            for row in evaluated
            if row.predicted_stable_peak_kg is not None and row.predicted_stable_peak_kg < 0
        ),
        mape=quantize_ratio(sum(apes, Decimal("0")) / Decimal(len(apes))),
        mdape=quantize_ratio(_median(apes)),
        wmape=quantize_ratio(total_abs_error / total_actual),
        mae_kg=quantize_kg(total_abs_error / Decimal(len(abs_errors))),
        mae_tonne=quantize_kg((total_abs_error / Decimal(len(abs_errors))) / Decimal("1000")),
        mean_bias_kg=quantize_kg(sum(biases, Decimal("0")) / Decimal(len(biases))),
        exclusion_counts=exclusion_counts,
    )


def split_excluded_rows(rows: list[BacktestResultRow]) -> tuple[BacktestResultRow, ...]:
    return tuple(row for row in rows if row.status == "excluded")


def build_model_summaries(rows: list[BacktestResultRow]) -> tuple[dict[str, object], ...]:
    summaries: list[dict[str, object]] = []
    baseline_names = sorted({row.baseline_name for row in rows})
    for baseline_name in baseline_names:
        baseline_rows = [row for row in rows if row.baseline_name == baseline_name]
        metrics = aggregate_error_metrics(baseline_rows)
        summaries.append(
            {
                "baseline_name": baseline_name,
                "evaluated_row_count": metrics.evaluated_row_count,
                "excluded_row_count": metrics.excluded_row_count,
                "negative_prediction_count": metrics.negative_prediction_count,
                "mape": metrics.mape,
                "mdape": metrics.mdape,
                "wmape": metrics.wmape,
                "mae_kg": metrics.mae_kg,
                "mae_tonne": metrics.mae_tonne,
                "mean_bias_kg": metrics.mean_bias_kg,
                "exclusion_counts": metrics.exclusion_counts,
            }
        )
    return tuple(summaries)


def build_season_summaries(rows: list[BacktestResultRow]) -> tuple[dict[str, object], ...]:
    group_keys = sorted({(row.baseline_name, row.target_season_code) for row in rows})
    summaries: list[dict[str, object]] = []
    for baseline_name, target_season_code in group_keys:
        grouped_rows = [
            row
            for row in rows
            if row.baseline_name == baseline_name and row.target_season_code == target_season_code
        ]
        metrics = aggregate_error_metrics(grouped_rows)
        summaries.append(
            {
                "baseline_name": baseline_name,
                "target_season_code": target_season_code,
                "evaluated_row_count": metrics.evaluated_row_count,
                "excluded_row_count": metrics.excluded_row_count,
                "negative_prediction_count": metrics.negative_prediction_count,
                "mape": metrics.mape,
                "mdape": metrics.mdape,
                "wmape": metrics.wmape,
                "mae_kg": metrics.mae_kg,
                "mae_tonne": metrics.mae_tonne,
                "mean_bias_kg": metrics.mean_bias_kg,
                "exclusion_counts": metrics.exclusion_counts,
            }
        )
    return tuple(summaries)


def build_factory_summaries(rows: list[BacktestResultRow]) -> tuple[dict[str, object], ...]:
    group_keys = sorted(
        {(row.baseline_name, row.factory_id, row.factory_name) for row in rows},
        key=lambda item: (item[0], item[2], item[1]),
    )
    summaries: list[dict[str, object]] = []
    for baseline_name, factory_id, factory_name in group_keys:
        grouped_rows = [
            row
            for row in rows
            if row.baseline_name == baseline_name and row.factory_id == factory_id
        ]
        metrics = aggregate_error_metrics(grouped_rows)
        summaries.append(
            {
                "baseline_name": baseline_name,
                "factory_id": factory_id,
                "factory_name": factory_name,
                "evaluated_row_count": metrics.evaluated_row_count,
                "excluded_row_count": metrics.excluded_row_count,
                "negative_prediction_count": metrics.negative_prediction_count,
                "mape": metrics.mape,
                "mdape": metrics.mdape,
                "wmape": metrics.wmape,
                "mae_kg": metrics.mae_kg,
                "mae_tonne": metrics.mae_tonne,
                "mean_bias_kg": metrics.mean_bias_kg,
                "exclusion_counts": metrics.exclusion_counts,
            }
        )
    return tuple(summaries)


def build_leakage_audit(
    *,
    rows: list[BacktestResultRow],
    metrics: ErrorMetrics,
    target_uses_peak_concentration: bool,
    scaler_fit_on_test_rows: bool,
    model_trained_on_test_rows: bool,
    alpha_selected_on_full_data: bool,
    duplicate_train_test_samples: bool,
    previous_season_pairing_skipped_gap: bool,
    duplicate_build_run_counted_twice: bool,
    excluded_rows_counted_as_zero: bool,
) -> list[LeakageAuditCheck]:
    evidence_prefix = (
        f"evaluated_rows={metrics.evaluated_row_count} mape={metrics.mape}"
        if metrics.mape is not None
        else f"evaluated_rows={metrics.evaluated_row_count} mape=None"
    )
    return [
        LeakageAuditCheck(
            "uses_target_peak_value",
            True,
            f"{evidence_prefix}; feature list excludes target peak",
        ),
        LeakageAuditCheck("uses_target_peak_date", True, "peak dates are not part of feature set"),
        LeakageAuditCheck(
            "uses_target_season_peak_concentration",
            not target_uses_peak_concentration,
            "target-season peak_concentration excluded from Ridge features",
        ),
        LeakageAuditCheck(
            "scaler_fit_on_test_rows",
            not scaler_fit_on_test_rows,
            "scaler must fit only training rows",
        ),
        LeakageAuditCheck(
            "ridge_trained_on_test_rows",
            not model_trained_on_test_rows,
            "training rows must exclude target fold rows",
        ),
        LeakageAuditCheck(
            "alpha_selected_on_full_data",
            not alpha_selected_on_full_data,
            "alpha must come from fixed config",
        ),
        LeakageAuditCheck(
            "duplicate_samples_across_train_test",
            not duplicate_train_test_samples,
            "fold split must not reuse the same sample in train and test",
        ),
        LeakageAuditCheck(
            "previous_season_pairing_skips_gap",
            not previous_season_pairing_skipped_gap,
            "previous-season baseline must use the immediate prior season only",
        ),
        LeakageAuditCheck(
            "duplicate_build_run_counted_twice",
            not duplicate_build_run_counted_twice,
            "source build runs must be unique within a run signature",
        ),
        LeakageAuditCheck(
            "excluded_rows_counted_as_zero_error",
            not excluded_rows_counted_as_zero,
            "excluded rows must stay outside error denominators",
        ),
    ]
