from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from backend.app.db.session import AsyncSessionMaker
from backend.app.planning.plan_config import load_production_plan_config
from backend.app.planning.plan_importer import import_production_plans_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import versioned production plans from CSV.")
    parser.add_argument("--file", required=True, help="CSV file path")
    parser.add_argument(
        "--config",
        default="configs/production_plan.yaml",
        help="Task 6 production-plan config path",
    )
    parser.add_argument(
        "--source-version",
        default=None,
        help="Optional source version override for imported rows",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    return parser


async def _run(args: argparse.Namespace) -> int:
    config = load_production_plan_config(Path(args.config))
    async with AsyncSessionMaker() as session:
        result = await import_production_plans_csv(
            session,
            file_path=Path(args.file),
            config=config,
            dry_run=bool(args.dry_run),
            source_version_override=args.source_version,
        )
    print(json.dumps(result.__dict__, ensure_ascii=False, default=str, indent=2))
    return 0 if result.status != "failed" else 1


def main() -> int:
    parser = build_parser()
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
