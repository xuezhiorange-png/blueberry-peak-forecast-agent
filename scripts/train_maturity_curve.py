from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if TYPE_CHECKING:
    from backend.app.maturity.schemas import MaturityManifestRow


NULLABLE_COLUMNS = frozenset(
    {
        "subfarm_id",
        "exclusion_reason",
    }
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train Task 8 natural maturity curve model")
    parser.add_argument("--file", required=True, help="Training manifest CSV path")
    parser.add_argument("--training-cutoff", required=True, help="Training cutoff ISO date")
    parser.add_argument("--config", default="configs/maturity_curve.yaml", help="Config path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and train without writing database rows",
    )
    parser.add_argument("--output", help="Optional JSON output path")
    parser.add_argument(
        "--output-dir",
        default="reports/maturity",
        help="Report output directory for JSON and Markdown artifacts",
    )
    return parser


def _normalize_csv_row(raw: dict[str, str | None]) -> dict[str, str | None]:
    normalized = dict(raw)
    for column in NULLABLE_COLUMNS:
        value = normalized.get(column)
        if value is None or value.strip() == "":
            normalized[column] = None
    return normalized


def _manifest_rows(path: Path) -> list[MaturityManifestRow]:
    from backend.app.maturity.schemas import MaturityManifestRow
    from backend.app.schemas.maturity import MaturityManifestRowInput

    rows: list[MaturityManifestRow] = []
    with path.open("r", encoding="utf-8") as file:
        for raw in csv.DictReader(file):
            parsed = MaturityManifestRowInput.model_validate(_normalize_csv_row(raw))
            rows.append(MaturityManifestRow(**parsed.model_dump()))
    return rows


def _write_output(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


async def _main() -> int:
    from backend.app.db.session import AsyncSessionMaker
    from backend.app.maturity.config import load_maturity_curve_config
    from backend.app.maturity.reporting import write_model_reports
    from backend.app.maturity.service import _model_payload, train_maturity_curve

    args = _parser().parse_args()
    config = load_maturity_curve_config(Path(args.config))
    manifest_rows = _manifest_rows(Path(args.file))

    async with AsyncSessionMaker() as session:
        result = await train_maturity_curve(
            session,
            training_cutoff=date.fromisoformat(args.training_cutoff),
            manifest_rows=manifest_rows,
            config=config,
            dry_run=args.dry_run,
        )
    payload = _model_payload(result)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    if args.output:
        _write_output(args.output, text)
    else:
        json_path, markdown_path = write_model_reports(
            result,
            output_dir=Path(args.output_dir),
        )
        print(text)
        print(f"report_json={json_path}")
        print(f"report_markdown={markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
