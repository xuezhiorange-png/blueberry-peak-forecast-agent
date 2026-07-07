from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from backend.app.baseline.json_types import canonical_json_value
from backend.app.planning.schemas import ClimateZoneImportExecutionResult


def climate_zone_report_payload(
    result: ClimateZoneImportExecutionResult,
) -> dict[str, Any]:
    return cast(dict[str, Any], canonical_json_value(asdict(result)))


def write_climate_zone_reports(
    *,
    report_dir: Path,
    sha_prefix: str,
    result: ClimateZoneImportExecutionResult,
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = climate_zone_report_payload(result)
    json_path = report_dir / f"climate_zone_import_{sha_prefix}.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    md_path = report_dir / f"climate_zone_import_{sha_prefix}.md"
    md_path.write_text(
        "\n".join(
            [
                f"# Climate zone import {sha_prefix}",
                f"- status: {result.status}",
                f"- zone_version: {result.zone_version}",
                f"- dry_run: {result.dry_run}",
                f"- total_rows: {result.total_rows}",
                f"- valid_rows: {result.valid_rows}",
                f"- invalid_rows: {result.invalid_rows}",
                f"- inserted_rows: {result.inserted_rows}",
                f"- skipped_rows: {result.skipped_rows}",
                f"- conflict_rows: {result.conflict_rows}",
                (f"- warnings: {', '.join(result.warnings) if result.warnings else '(none)'}"),
                f"- error_message: {result.error_message or '(none)'}",
            ]
        ),
        encoding="utf-8",
    )
    return json_path, md_path
