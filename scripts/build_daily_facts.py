from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict
from pathlib import Path

from backend.app.analytics.config import load_analytics_config
from backend.app.analytics.daily_facts import (
    DailyFactsBuildResult,
    build_daily_facts_for_season,
    dry_run_daily_facts_for_season,
)
from backend.app.db.session import AsyncSessionMaker, dispose_db_engine
from backend.app.etl.history.quality import decimal_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build versioned daily facts and peak metrics for a season."
    )
    parser.add_argument("--season-code", required=True)
    parser.add_argument("--config", default="configs/analytics_rules.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-dir", default="reports/analytics")
    parser.add_argument("--log-level", default="INFO")
    return parser


def _result_payload(result: DailyFactsBuildResult) -> dict[str, object]:
    return decimal_json(asdict(result))


def _markdown_summary(result: DailyFactsBuildResult) -> str:
    lines = [
        f"# Analytics Build Report: {result.season_code}",
        "",
        f"- status: {result.status}",
        f"- aggregation_version: {result.aggregation_version}",
        f"- source_max_raw_id: {result.source_max_raw_id}",
        f"- config_hash: {result.config_hash}",
        f"- source_eligible_row_count: {result.source_eligible_row_count}",
        f"- source_eligible_weight_kg: {result.source_eligible_weight_kg}",
        f"- daily_fact_row_count: {result.daily_fact_row_count}",
        f"- factory_count: {result.factory_count}",
        f"- metric_row_count: {result.metric_row_count}",
    ]
    if result.error_message:
        lines.append(f"- error_message: {result.error_message}")
    if result.factory_summaries:
        lines.extend(["", "## Factories", ""])
        for summary in result.factory_summaries:
            lines.extend(
                [
                    f"### Factory {summary.factory_id}",
                    f"- total_weight_kg: {summary.total_weight_kg}",
                    f"- single_day_peak_kg: {summary.single_day_peak_kg}",
                    f"- single_day_peak_date: {summary.single_day_peak_date}",
                    f"- stable_median_3d_peak_kg: {summary.stable_median_3d_peak_kg}",
                    f"- stable_median_3d_peak_date: {summary.stable_median_3d_peak_date}",
                    f"- mean_3d_peak_kg: {summary.mean_3d_peak_kg}",
                    f"- mean_3d_peak_date: {summary.mean_3d_peak_date}",
                    f"- peak_concentration: {summary.peak_concentration}",
                    f"- variety_hhi: {summary.variety_hhi}",
                    f"- farm_hhi: {summary.farm_hhi}",
                    f"- subfarm_hhi: {summary.subfarm_hhi}",
                    f"- unknown_farm_weight_share: {summary.unknown_farm_weight_share}",
                    f"- unknown_subfarm_weight_share: {summary.unknown_subfarm_weight_share}",
                    f"- spring_festival_day_count: {summary.spring_festival_day_count}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _write_reports(result: DailyFactsBuildResult, report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{result.season_code}.{result.source_max_raw_id}.{result.config_hash[:12]}"
    (report_dir / f"{base_name}.json").write_text(
        json.dumps(_result_payload(result), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (report_dir / f"{base_name}.md").write_text(
        _markdown_summary(result),
        encoding="utf-8",
    )


async def _run() -> int:
    args = _parser().parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper()))
    config = load_analytics_config(Path(args.config))
    async with AsyncSessionMaker() as session:
        result = (
            await dry_run_daily_facts_for_season(session, args.season_code, config)
            if args.dry_run
            else await build_daily_facts_for_season(session, args.season_code, config)
        )
    _write_reports(result, Path(args.report_dir))
    logging.info(
        "season=%s status=%s cutoff=%s daily_rows=%s factories=%s",
        result.season_code,
        result.status,
        result.source_max_raw_id,
        result.daily_fact_row_count,
        result.factory_count,
    )
    await dispose_db_engine()
    return 1 if result.status == "failed" else 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
