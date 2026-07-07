from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict
from pathlib import Path

from backend.app.baseline.json_types import canonical_json_value
from backend.app.db.session import AsyncSessionMaker, dispose_db_engine
from backend.app.planning.importers import import_location_references_csv
from backend.app.planning.schemas import ImportExecutionResult


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import Task 5 location references CSV.")
    parser.add_argument("--file", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--report-dir", default="reports/parameter-inference")
    parser.add_argument("--log-level", default="INFO")
    return parser


def _write_report(report_dir: Path, version: str, result: ImportExecutionResult) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_value(asdict(result))
    output_path = report_dir / f"location-import-{version}.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


async def _run() -> int:
    args = _parser().parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    async with AsyncSessionMaker() as session:
        result = await import_location_references_csv(
            session,
            file_path=Path(args.file),
            source_version=args.version,
            dry_run=args.dry_run,
        )
    _write_report(Path(args.report_dir), args.version, result)
    if args.activate:
        logging.info(
            "location reference import ignores --activate; versions are source scoped only"
        )
    logging.info(
        "status=%s inserted=%s skipped=%s sha=%s",
        result.status,
        result.inserted_row_count,
        result.skipped_row_count,
        result.file_sha256,
    )
    await dispose_db_engine()
    return 1 if result.status == "failed" else 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
