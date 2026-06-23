from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if TYPE_CHECKING:
    from backend.app.weather.schemas import BaseTemperatureTrainingSample


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Task 7 base-temperature candidate search.")
    parser.add_argument("--file", required=True)
    parser.add_argument("--training-cutoff", required=True)
    parser.add_argument("--scope-type", default="variety")
    parser.add_argument("--variety-id", type=int)
    parser.add_argument("--climate-zone-id", type=int)
    parser.add_argument("--config", default="configs/weather_features.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", default="reports/weather")
    parser.add_argument("--log-level", default="INFO")
    return parser


def _load_samples(file_path: Path) -> list[BaseTemperatureTrainingSample]:
    from backend.app.weather.schemas import BaseTemperatureTrainingSample

    with file_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    samples: list[BaseTemperatureTrainingSample] = []
    for row in rows:
        samples.append(
            BaseTemperatureTrainingSample(
                plan_id=int(row["plan_id"]),
                anchor_event=str(row["anchor_event"]).strip(),
                target_event=str(row["target_event"]).strip(),
                sample_weight=Decimal(str(row.get("sample_weight") or "1")),
                include=str(row.get("include") or "true").strip().lower() in {"1", "true", "yes"},
                exclusion_reason=(str(row["exclusion_reason"]).strip() or None)
                if row.get("exclusion_reason") is not None
                else None,
            )
        )
    return samples


def _write_report(output_dir: Path, source_signature: str, payload: dict[str, object]) -> None:
    from backend.app.planning.json_types import canonical_json_value

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"base-temperature-search-{source_signature[:12] or 'preview'}.json"
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
    from backend.app.weather.config import load_weather_feature_config
    from backend.app.weather.service import _base_temperature_payload, search_base_temperature

    args = _parser().parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    config = load_weather_feature_config(Path(args.config))
    samples = _load_samples(Path(args.file))
    async with AsyncSessionMaker() as session:
        result = await search_base_temperature(
            session,
            training_cutoff=date.fromisoformat(args.training_cutoff),
            samples=samples,
            config=config,
            variety_id=args.variety_id,
            climate_zone_id=args.climate_zone_id,
            scope_type=args.scope_type,
            dry_run=args.dry_run,
        )
    _write_report(
        Path(args.output_dir),
        result.source_signature,
        _base_temperature_payload(result),
    )
    logging.info(
        "status=%s run_id=%s selected_base_temperature=%s",
        result.status,
        result.run_id,
        result.selected_base_temperature,
    )
    await dispose_db_engine()
    return 1 if result.status == "failed" else 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
