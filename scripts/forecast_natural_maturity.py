from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forecast Task 8 natural maturity curve")
    parser.add_argument("--model-run-id", required=True, type=int)
    parser.add_argument("--farm-id", required=True, type=int)
    parser.add_argument("--season-id", required=True, type=int)
    parser.add_argument("--variety-id", required=True, type=int)
    parser.add_argument("--subfarm-id", type=int)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--prediction-start-date", required=True)
    parser.add_argument("--prediction-end-date", required=True)
    parser.add_argument("--facility-type", required=True)
    parser.add_argument("--expected-marketable-total-kg")
    parser.add_argument("--config", default="configs/maturity_curve.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output")
    parser.add_argument(
        "--output-dir",
        default="reports/maturity",
        help="Report output directory for JSON and Markdown artifacts",
    )
    return parser


def _write_output(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


async def _main() -> int:
    from backend.app.db.session import AsyncSessionMaker
    from backend.app.maturity.config import load_maturity_curve_config
    from backend.app.maturity.reporting import write_forecast_reports
    from backend.app.maturity.service import _forecast_payload, forecast_natural_maturity

    args = _parser().parse_args()

    config = load_maturity_curve_config(Path(args.config))
    expected_total = (
        None
        if args.expected_marketable_total_kg is None
        else Decimal(args.expected_marketable_total_kg)
    )
    async with AsyncSessionMaker() as session:
        result = await forecast_natural_maturity(
            session,
            model_run_id=args.model_run_id,
            farm_id=args.farm_id,
            subfarm_id=args.subfarm_id,
            season_id=args.season_id,
            variety_id=args.variety_id,
            as_of_date=date.fromisoformat(args.as_of_date),
            prediction_start_date=date.fromisoformat(args.prediction_start_date),
            prediction_end_date=date.fromisoformat(args.prediction_end_date),
            expected_marketable_total_kg=expected_total,
            facility_type=args.facility_type,
            config=config,
            dry_run=args.dry_run,
        )
    payload = _forecast_payload(result)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    if args.output:
        _write_output(args.output, text)
    else:
        json_path, markdown_path = write_forecast_reports(
            result,
            output_dir=Path(args.output_dir),
        )
        print(text)
        print(f"report_json={json_path}")
        print(f"report_markdown={markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
