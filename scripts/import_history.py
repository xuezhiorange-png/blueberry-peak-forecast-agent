from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from backend.app.db.session import AsyncSessionMaker, dispose_db_engine
from backend.app.etl.history.config import load_import_config
from backend.app.etl.history.importer import ImportFatalError, dry_run_source, import_source
from backend.app.etl.history.quality import decimal_json
from backend.app.etl.history.schemas import ImportResult


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import historical factory receipt .xls files.")
    parser.add_argument("--manifest", default="configs/source_manifest.yaml")
    parser.add_argument("--rules", default="configs/import_rules.yaml")
    parser.add_argument("--factory-aliases", default="configs/factory_aliases.yaml")
    parser.add_argument("--variety-aliases", default="configs/variety_aliases.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-file")
    parser.add_argument("--report-dir", default="reports/import")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser


def _write_report(result: ImportResult, report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{Path(result.source_path).name}.{result.file_sha256[:12]}.json"
    report_path.write_text(
        json.dumps(decimal_json(result.report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


async def _run() -> int:
    args = _parser().parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper()))
    config = load_import_config(
        Path(args.manifest),
        Path(args.rules),
        Path(args.factory_aliases),
        Path(args.variety_aliases),
    )
    failures = 0
    async with AsyncSessionMaker() as session:
        for source in config.sources:
            if not source.enabled:
                continue
            if args.only_file and Path(args.only_file).name != source.path.name:
                continue
            try:
                result = (
                    await dry_run_source(session, source, config, Path("."))
                    if args.dry_run
                    else await import_source(session, source, config, Path("."))
                )
            except ImportFatalError as exc:
                failures += 1
                logging.error("%s", exc)
                if args.fail_fast:
                    break
                continue
            _write_report(result, Path(args.report_dir))
            logging.info(
                "%s status=%s sha=%s inserted=%s rows=%s",
                source.path.name,
                result.status,
                result.file_sha256[:12],
                result.inserted_row_count,
                result.report.row_count,
            )
    await dispose_db_engine()
    return 1 if failures else 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
