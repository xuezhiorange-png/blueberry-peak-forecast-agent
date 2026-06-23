from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Task 7 weather window features.")
    parser.add_argument("--farm-id", required=True, type=int)
    parser.add_argument("--season-id", required=True, type=int)
    parser.add_argument("--variety-id", required=True, type=int)
    parser.add_argument("--subfarm-id", type=int)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--feature-date", required=True)
    parser.add_argument("--config", default="configs/weather_features.yaml")
    parser.add_argument("--production-plan-config", default="configs/production_plan.yaml")
    parser.add_argument("--base-temperature-search-run-id", type=int)
    parser.add_argument("--anchor-event")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", default="reports/weather")
    parser.add_argument("--log-level", default="INFO")
    return parser


def _write_report(output_dir: Path, source_signature: str, payload: dict[str, object]) -> None:
    from backend.app.planning.json_types import canonical_json_value

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"weather-feature-{source_signature[:12] or 'preview'}.json"
    path.write_text(
        json.dumps(
            canonical_json_value(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


async def _run() -> int:
    from backend.app.db.session import AsyncSessionMaker, dispose_db_engine
    from backend.app.planning.plan_config import load_production_plan_config
    from backend.app.weather.config import load_weather_feature_config
    from backend.app.weather.service import (
        _weather_feature_payload,
        compute_weather_window_features,
    )

    args = _parser().parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    weather_config = load_weather_feature_config(Path(args.config))
    plan_config = load_production_plan_config(Path(args.production_plan_config))
    async with AsyncSessionMaker() as session:
        result = await compute_weather_window_features(
            session,
            farm_id=args.farm_id,
            subfarm_id=args.subfarm_id,
            season_id=args.season_id,
            variety_id=args.variety_id,
            as_of_date=date.fromisoformat(args.as_of_date),
            feature_date=date.fromisoformat(args.feature_date),
            config=weather_config,
            production_plan_config=plan_config,
            base_temperature_search_run_id=args.base_temperature_search_run_id,
            anchor_event=args.anchor_event,
            dry_run=args.dry_run,
        )
    _write_report(
        Path(args.output_dir),
        result.source_signature,
        _weather_feature_payload(result),
    )
    logging.info("status=%s run_id=%s", result.status, result.run_id)
    await dispose_db_engine()
    return 1 if result.status == "failed" else 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
