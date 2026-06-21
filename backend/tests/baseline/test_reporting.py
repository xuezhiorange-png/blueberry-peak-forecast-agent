from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from backend.app.baseline.reporting import write_execution_reports
from backend.app.baseline.schemas import (
    BacktestResultRow,
    BaselineBacktestExecutionResult,
    LeakageAuditCheck,
)


def _execution_result() -> BaselineBacktestExecutionResult:
    row = BacktestResultRow(
        baseline_name="previous_season_peak",
        target_season_id=1,
        target_season_code="2024-2025",
        factory_id=1,
        factory_name="Factory A",
        previous_season_id=None,
        previous_season_code=None,
        fold_key="season:2024-2025",
        status="evaluated",
        actual_stable_peak_kg=Decimal("100.000000"),
        predicted_stable_peak_kg=Decimal("95.500000"),
        absolute_error_kg=Decimal("4.500000"),
        signed_error_kg=Decimal("-4.500000"),
        ape=Decimal("0.0450000000"),
        input_features={"previous_season_stable_peak_kg": "100.000000"},
        training_season_codes=["2023-2024"],
        model_metadata={"feature_names": ["total_weight_kg"]},
    )
    return BaselineBacktestExecutionResult(
        status="completed",
        run_id=42,
        model_version="task4-baseline-v1",
        benchmark_mode="historical_oracle",
        production_eligible=False,
        source_signature="source-signature",
        source_build_runs=(
            {
                "season_code": "2024-2025",
                "build_run_id": 10,
                "aggregation_version": "task3-v1",
                "source_max_raw_id": 100,
                "config_hash": "task3-cfg",
            },
        ),
        evaluation_scheme="leave_one_season_out",
        result_row_count=1,
        model_summaries=(
            {
                "baseline_name": "previous_season_peak",
                "evaluated_row_count": 1,
                "excluded_row_count": 0,
                "negative_prediction_count": 0,
                "mape": Decimal("0.0450000000"),
                "mdape": Decimal("0.0450000000"),
                "wmape": Decimal("0.0450000000"),
                "mae_kg": Decimal("4.500000"),
                "mae_tonne": Decimal("0.004500"),
                "mean_bias_kg": Decimal("-4.500000"),
                "exclusion_counts": {},
            },
        ),
        season_summaries=(),
        factory_summaries=(),
        results=(row,),
        excluded_rows=(),
        leakage_audit=(
            LeakageAuditCheck(
                name="target peak leakage",
                passed=True,
                evidence="not present",
            ),
        ),
        limitations=("production_eligible=false",),
        database_completed=True,
    )


def test_write_execution_reports_serializes_decimals_in_nested_tuples(tmp_path: Path) -> None:
    result = _execution_result()

    written = write_execution_reports(result, output_dir=tmp_path)

    json_path = Path(written.report_paths[0])
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert payload["results"][0]["actual_stable_peak_kg"] == "100.000000"
    assert payload["model_summaries"][0]["mape"] == "0.0450000000"
