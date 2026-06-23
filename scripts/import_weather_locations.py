from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import Task 7 weather source locations CSV.")
    parser.add_argument("--file", required=True)
    parser.add_argument("--provider-code", required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--location-type", choices=("station", "grid"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", default="reports/weather")
    parser.add_argument("--log-level", default="INFO")
    return parser


def _write_report(output_dir: Path, file_name: str, payload: dict[str, object]) -> None:
    from backend.app.planning.json_types import canonical_json_value

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"weather-locations-{Path(file_name).stem}.json"
    path.write_text(
        json.dumps(canonical_json_value(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _log_summary(payload: dict[str, object]) -> None:
    logging.info(
        "status=%s inserted=%s skipped=%s",
        payload["status"],
        payload.get("inserted_count"),
        payload.get("skipped_count"),
    )


async def _run() -> int:
    from backend.app.db.session import AsyncSessionMaker, dispose_db_engine
    from backend.app.weather.service import import_weather_locations

    args = _parser().parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    async with AsyncSessionMaker() as session:
        result = await import_weather_locations(
            session,
            file_path=Path(args.file),
            provider_code=args.provider_code,
            dataset_version=args.source_version,
            location_type=args.location_type,
            dry_run=args.dry_run,
        )
    _write_report(Path(args.output_dir), args.file, result)
    _log_summary(result)
    await dispose_db_engine()
    return 1 if result["status"] == "failed" else 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
