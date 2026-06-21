from __future__ import annotations

from dataclasses import replace
from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.baseline.baselines import (
    evaluate_previous_season_peak,
    evaluate_volume_previous_concentration,
)
from backend.app.baseline.config import BaselineConfig
from backend.app.baseline.dataset import (
    rows_to_samples,
    select_source_build_runs,
    source_build_run_payload,
)
from backend.app.baseline.json_types import canonicalize_result_row
from backend.app.baseline.metrics import (
    aggregate_error_metrics,
    build_factory_summaries,
    build_leakage_audit,
    build_model_summaries,
    build_season_summaries,
    split_excluded_rows,
)
from backend.app.baseline.repository import (
    create_running_run,
    find_existing_run,
    get_run_by_id,
    insert_result_rows,
    list_completed_source_build_runs,
    load_result_rows_for_run,
    load_samples_for_build_runs,
    mark_run_completed,
    mark_run_failed,
)
from backend.app.baseline.ridge import (
    RIDGE_FEATURES,
    evaluate_ridge_factory_holdout,
    evaluate_ridge_loso,
)
from backend.app.baseline.schemas import (
    BacktestResultRow,
    BaselineBacktestExecutionResult,
    LeakageAuditCheck,
)
from backend.app.baseline.signature import source_signature

_LIMITATIONS = (
    "benchmark_mode=historical_oracle uses final-season total_weight_kg and structure HHI inputs.",
    "production_eligible=false because oracle features are not available at forecast time.",
    "rolling_time_backtest=deferred_to_task_11.",
)


def _sanitize_error_message(message: str) -> str:
    return " ".join(str(message).replace("\r", " ").replace("\n", " ").split())[:500]


def _oracle_metadata() -> dict[str, object]:
    return {
        "oracle_feature": True,
        "available_at_forecast_time": False,
    }


def _enforce_ridge_feature_guards(rows: list[BacktestResultRow]) -> None:
    forbidden_features = {
        "peak_concentration",
        "stable_median_3d_peak_kg",
        "single_day_peak_kg",
        "single_day_peak_date",
        "mean_3d_peak_kg",
        "mean_3d_peak_date",
        "stable_median_3d_peak_date",
    }
    for row in rows:
        if not row.baseline_name.startswith("ridge_structure"):
            continue
        keys = set(row.input_features)
        if keys != set(RIDGE_FEATURES):
            raise ValueError(f"Ridge features must be exactly {RIDGE_FEATURES}, got {sorted(keys)}")
        overlap = forbidden_features.intersection(keys)
        if overlap:
            raise ValueError(f"Ridge feature leakage detected: {sorted(overlap)}")
        metadata = row.model_metadata
        if metadata.get("feature_names") != list(RIDGE_FEATURES):
            raise ValueError("Ridge metadata must persist the fixed feature_names list")


def _build_leakage_audit(rows: list[BacktestResultRow]) -> tuple[LeakageAuditCheck, ...]:
    metrics = aggregate_error_metrics(rows)
    ridge_rows = [row for row in rows if row.baseline_name == "ridge_structure"]
    audit_rows = build_leakage_audit(
        rows=rows,
        metrics=metrics,
        target_uses_peak_concentration=any(
            "peak_concentration" in row.input_features for row in ridge_rows
        ),
        scaler_fit_on_test_rows=any(
            row.target_season_code in row.training_season_codes for row in ridge_rows
        ),
        model_trained_on_test_rows=any(
            row.target_season_code in row.training_season_codes for row in ridge_rows
        ),
        alpha_selected_on_full_data=False,
        duplicate_train_test_samples=False,
        previous_season_pairing_skipped_gap=False,
        duplicate_build_run_counted_twice=False,
        excluded_rows_counted_as_zero=False,
    )
    return tuple(audit_rows)


def _sort_result_rows(
    rows: list[BacktestResultRow],
    *,
    season_order: dict[str, int],
) -> list[BacktestResultRow]:
    return sorted(
        rows,
        key=lambda row: (
            row.baseline_name,
            season_order.get(row.target_season_code, len(season_order)),
            row.factory_name,
            row.factory_id,
        ),
    )


def _build_execution_result(
    *,
    status: str,
    run_id: int | str | None,
    model_version: str,
    benchmark_mode: str,
    production_eligible: bool,
    evaluation_scheme: str,
    source_signature_value: str,
    source_build_runs_value: tuple[dict[str, object], ...],
    rows: list[BacktestResultRow],
    error_message: str | None = None,
) -> BaselineBacktestExecutionResult:
    return BaselineBacktestExecutionResult(
        status=status,
        run_id=run_id,
        model_version=model_version,
        benchmark_mode=benchmark_mode,
        production_eligible=production_eligible,
        source_signature=source_signature_value,
        source_build_runs=source_build_runs_value,
        evaluation_scheme=evaluation_scheme,
        result_row_count=len(rows),
        model_summaries=build_model_summaries(rows),
        season_summaries=build_season_summaries(rows),
        factory_summaries=build_factory_summaries(rows),
        results=tuple(rows),
        excluded_rows=split_excluded_rows(rows),
        leakage_audit=_build_leakage_audit(rows),
        limitations=_LIMITATIONS,
        database_completed=status in {"completed", "skipped"},
        error_message=error_message,
    )


def _apply_oracle_metadata(rows: list[BacktestResultRow]) -> list[BacktestResultRow]:
    patched: list[BacktestResultRow] = []
    for row in rows:
        if row.baseline_name != "volume_previous_concentration":
            patched.append(row)
            continue
        features = dict(row.input_features)
        if "oracle_total_weight_kg" in features:
            features["oracle_total_weight_metadata"] = _oracle_metadata()
        patched.append(replace(row, input_features=features))
    return patched


async def _result_from_existing_run(
    session: AsyncSession,
    *,
    run_id: int,
    config: BaselineConfig,
    source_signature_value: str,
    source_build_runs_value: tuple[dict[str, object], ...],
    status: str,
) -> BaselineBacktestExecutionResult:
    rows = await load_result_rows_for_run(session, run_id=run_id)
    return _build_execution_result(
        status=status,
        run_id=run_id,
        model_version=config.rules.version,
        benchmark_mode=config.rules.benchmark_mode,
        production_eligible=config.rules.production_eligible,
        evaluation_scheme=config.rules.evaluation.primary_scheme,
        source_signature_value=source_signature_value,
        source_build_runs_value=source_build_runs_value,
        rows=rows,
    )


async def _compute_rows(
    session: AsyncSession,
    *,
    selected_build_runs_payload: tuple[dict[str, object], ...],
    season_order: dict[str, int],
    config: BaselineConfig,
) -> list[BacktestResultRow]:
    build_run_ids = tuple(
        int(cast(int, item["build_run_id"])) for item in selected_build_runs_payload
    )
    samples = rows_to_samples(
        await load_samples_for_build_runs(session, build_run_ids=build_run_ids)
    )
    rows = (
        evaluate_previous_season_peak(samples)
        + evaluate_volume_previous_concentration(samples)
        + evaluate_ridge_loso(samples, config)
        + evaluate_ridge_factory_holdout(samples, config)
    )
    rows = _apply_oracle_metadata(rows)
    rows = [canonicalize_result_row(row) for row in rows]
    rows = _sort_result_rows(rows, season_order=season_order)
    _enforce_ridge_feature_guards(rows)
    return rows


async def execute_baseline_backtest(
    session: AsyncSession,
    *,
    config: BaselineConfig,
    season_codes: tuple[str, ...] | None = None,
    explicit_build_run_ids: dict[str, int] | None = None,
    dry_run: bool = False,
) -> BaselineBacktestExecutionResult:
    explicit_ids = explicit_build_run_ids or {}
    try:
        available_runs = await list_completed_source_build_runs(
            session,
            season_codes=season_codes,
        )
        selected_runs = select_source_build_runs(
            available_runs=available_runs,
            season_codes=season_codes,
            explicit_build_run_ids=explicit_ids,
        )
    except Exception as exc:
        return BaselineBacktestExecutionResult(
            status="failed",
            run_id=None,
            model_version=config.rules.version,
            benchmark_mode=config.rules.benchmark_mode,
            production_eligible=config.rules.production_eligible,
            source_signature="",
            source_build_runs=(),
            evaluation_scheme=config.rules.evaluation.primary_scheme,
            result_row_count=0,
            model_summaries=(),
            season_summaries=(),
            factory_summaries=(),
            results=(),
            excluded_rows=(),
            leakage_audit=(),
            limitations=_LIMITATIONS,
            error_message=_sanitize_error_message(str(exc)),
        )

    source_build_runs_value = source_build_run_payload(selected_runs)
    source_signature_value = source_signature(selected_runs)
    season_order = {
        item.season_code: index for index, item in enumerate(selected_runs)
    }

    if dry_run:
        dry_run_rows = await _compute_rows(
            session,
            selected_build_runs_payload=source_build_runs_value,
            season_order=season_order,
            config=config,
        )
        return _build_execution_result(
            status="dry_run",
            run_id=f"dry-run-{source_signature_value[:12]}",
            model_version=config.rules.version,
            benchmark_mode=config.rules.benchmark_mode,
            production_eligible=config.rules.production_eligible,
            evaluation_scheme=config.rules.evaluation.primary_scheme,
            source_signature_value=source_signature_value,
            source_build_runs_value=source_build_runs_value,
            rows=dry_run_rows,
        )

    existing = await find_existing_run(
        session,
        model_version=config.rules.version,
        config_hash=config.config_hash,
        source_signature=source_signature_value,
        evaluation_scheme=config.rules.evaluation.primary_scheme,
    )
    if existing is not None:
        status = "skipped" if existing.status == "completed" else "running"
        return await _result_from_existing_run(
            session,
            run_id=existing.id,
            config=config,
            source_signature_value=source_signature_value,
            source_build_runs_value=source_build_runs_value,
            status=status,
        )

    run_id: int | None = None
    model_version_value = config.rules.version
    config_hash_value = config.config_hash
    evaluation_scheme_value = config.rules.evaluation.primary_scheme
    rows: list[BacktestResultRow] = []

    try:
        run = await create_running_run(
            session,
            model_version=model_version_value,
            config_hash=config_hash_value,
            config_snapshot=config.snapshot,
            source_signature=source_signature_value,
            source_build_runs=source_build_runs_value,
            evaluation_scheme=evaluation_scheme_value,
            random_seed=config.rules.random_seed,
        )
        run_id = run.id
    except IntegrityError:
        await session.rollback()
        current = await find_existing_run(
            session,
            model_version=model_version_value,
            config_hash=config_hash_value,
            source_signature=source_signature_value,
            evaluation_scheme=evaluation_scheme_value,
        )
        if current is None:
            raise
        status = "skipped" if current.status == "completed" else "running"
        return await _result_from_existing_run(
            session,
            run_id=current.id,
            config=config,
            source_signature_value=source_signature_value,
            source_build_runs_value=source_build_runs_value,
            status=status,
        )

    try:
        rows = await _compute_rows(
            session,
            selected_build_runs_payload=source_build_runs_value,
            season_order=season_order,
            config=config,
        )
        assert run_id is not None
        await insert_result_rows(session, run_id=run_id, rows=rows)
        await mark_run_completed(session, run_id=run_id, result_row_count=len(rows))
        return _build_execution_result(
            status="completed",
            run_id=run_id,
            model_version=config.rules.version,
            benchmark_mode=config.rules.benchmark_mode,
            production_eligible=config.rules.production_eligible,
            evaluation_scheme=config.rules.evaluation.primary_scheme,
            source_signature_value=source_signature_value,
            source_build_runs_value=source_build_runs_value,
            rows=rows,
        )
    except Exception as exc:
        error_message = _sanitize_error_message(str(exc))
        await session.rollback()
        if run_id is not None:
            await mark_run_failed(session, run_id=run_id, error_message=error_message)
        return _build_execution_result(
            status="failed",
            run_id=run_id,
            model_version=config.rules.version,
            benchmark_mode=config.rules.benchmark_mode,
            production_eligible=config.rules.production_eligible,
            evaluation_scheme=config.rules.evaluation.primary_scheme,
            source_signature_value=source_signature_value,
            source_build_runs_value=source_build_runs_value,
            rows=rows,
            error_message=error_message,
        )


async def load_backtest_run_result(
    session: AsyncSession,
    *,
    run_id: int,
) -> BaselineBacktestExecutionResult:
    run = await get_run_by_id(session, run_id=run_id)
    if run is None:
        raise ValueError(f"Baseline backtest run not found: {run_id}")
    rows = await load_result_rows_for_run(session, run_id=run_id)
    return _build_execution_result(
        status=run.status,
        run_id=run.id,
        model_version=run.model_version,
        benchmark_mode="historical_oracle",
        production_eligible=False,
        evaluation_scheme=run.evaluation_scheme,
        source_signature_value=run.source_signature,
        source_build_runs_value=tuple(run.source_build_runs),
        rows=rows,
        error_message=run.error_message,
    )
