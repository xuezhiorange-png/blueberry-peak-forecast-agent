from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from backend.app.baseline.config import load_baseline_config
from backend.app.baseline.reporting import write_execution_reports
from backend.app.baseline.service import execute_baseline_backtest, load_backtest_run_result
from backend.app.db.session import AsyncSessionMaker, dispose_db_engine


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Task 4 baseline backtests against Task 3 daily-fact metrics."
    )
    parser.add_argument("--config", default="configs/baseline_model.yaml")
    parser.add_argument("--season", action="append", dest="seasons")
    parser.add_argument("--build-run", action="append", dest="build_runs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", default="reports/baseline")
    parser.add_argument("--report-run-id", type=int)
    parser.add_argument("--log-level", default="INFO")
    return parser


def _parse_build_run_overrides(values: list[str] | None) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"Invalid --build-run value: {value}")
        season_code, run_id_text = value.split("=", 1)
        season_code = season_code.strip()
        if not season_code:
            raise ValueError(f"Invalid --build-run season code: {value}")
        try:
            run_id = int(run_id_text)
        except ValueError as exc:
            raise ValueError(f"Invalid --build-run id: {value}") from exc
        overrides[season_code] = run_id
    return overrides


async def _run() -> int:
    args = _parser().parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    output_dir = Path(args.output_dir)
    try:
        explicit_build_runs = _parse_build_run_overrides(args.build_runs)
        async with AsyncSessionMaker() as session:
            if args.report_run_id is not None:
                result = await load_backtest_run_result(session, run_id=args.report_run_id)
            else:
                config = load_baseline_config(Path(args.config))
                result = await execute_baseline_backtest(
                    session,
                    config=config,
                    season_codes=tuple(args.seasons) if args.seasons else None,
                    explicit_build_run_ids=explicit_build_runs,
                    dry_run=args.dry_run,
                )
        try:
            result = write_execution_reports(result, output_dir=output_dir)
        except Exception as exc:
            logging.error(
                "database_completed=%s report_generation_failed=true error=%s",
                result.database_completed,
                exc,
            )
            return 1
        logging.info(
            "status=%s run_id=%s rows=%s source_signature=%s",
            result.status,
            result.run_id,
            result.result_row_count,
            result.source_signature,
        )
        return 1 if result.status == "failed" else 0
    finally:
        await dispose_db_engine()


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
