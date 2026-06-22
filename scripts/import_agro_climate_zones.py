from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from backend.app.db.session import AsyncSessionMaker, dispose_db_engine
from backend.app.planning.imports.climate_zone_importer import import_agro_climate_zones_csv
from backend.app.planning.imports.climate_zone_reporting import write_climate_zone_reports


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import Task 5 agro climate zones CSV.")
    parser.add_argument("--file", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-dir", default="reports/planning")
    parser.add_argument("--zone-version")
    parser.add_argument("--source-name")
    parser.add_argument("--source-version")
    parser.add_argument("--log-level", default="INFO")
    return parser


async def _run() -> int:
    args = _parser().parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    async with AsyncSessionMaker() as session:
        result = await import_agro_climate_zones_csv(
            session,
            file_path=Path(args.file),
            dry_run=args.dry_run,
            zone_version_override=args.zone_version,
            source_name_override=args.source_name,
            source_version_override=args.source_version,
        )
    sha_prefix = result.file_sha256[:12]
    write_climate_zone_reports(
        report_dir=Path(args.report_dir),
        sha_prefix=sha_prefix,
        result=result,
    )
    logging.info(
        "status=%s total=%s valid=%s invalid=%s inserted=%s skipped=%s conflicts=%s sha=%s",
        result.status,
        result.total_rows,
        result.valid_rows,
        result.invalid_rows,
        result.inserted_rows,
        result.skipped_rows,
        result.conflict_rows,
        result.file_sha256,
    )
    await dispose_db_engine()
    return 1 if result.status == "failed" else 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
