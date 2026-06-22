from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict
from pathlib import Path

from backend.app.baseline.json_types import canonical_json_value
from backend.app.db.session import AsyncSessionMaker, dispose_db_engine
from backend.app.planning.config import load_parameter_inference_config
from backend.app.planning.schemas import ParameterInferenceExecutionResult
from backend.app.planning.service import create_minimal_planning_task


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a Task 5 minimal planning task.")
    parser.add_argument("--address")
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--altitude-m", type=float)
    parser.add_argument("--variety-area", action="append", required=True)
    parser.add_argument("--as-of-date")
    parser.add_argument("--library-version")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", default="configs/parameter_inference.yaml")
    parser.add_argument("--output", default="reports/parameter-inference/task5-preview.json")
    parser.add_argument("--log-level", default="INFO")
    return parser


def _parse_variety_area(values: list[str]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for value in values:
        if "=" not in value:
            raise ValueError(f"invalid --variety-area: {value}")
        variety_code, area_text = value.split("=", 1)
        variety_code = variety_code.strip()
        area_text = area_text.strip()
        if not variety_code or not area_text:
            raise ValueError(f"invalid --variety-area: {value}")
        items.append({"variety_code": variety_code, "planted_area_mu": area_text})
    return items


def _build_location(args: argparse.Namespace) -> dict[str, object]:
    has_address = args.address is not None
    has_coordinates = args.latitude is not None or args.longitude is not None
    if has_address and has_coordinates:
        raise ValueError("address and latitude/longitude are mutually exclusive")
    if has_coordinates and (args.latitude is None or args.longitude is None):
        raise ValueError("latitude and longitude must be provided together")
    if not has_address and not has_coordinates:
        raise ValueError("one of --address or --latitude/--longitude is required")
    if has_address:
        location: dict[str, object] = {"address": args.address}
    else:
        location = {"latitude": args.latitude, "longitude": args.longitude}
    if args.altitude_m is not None:
        location["altitude_m"] = args.altitude_m
    return location


def _write_result(output_path: Path, result: ParameterInferenceExecutionResult) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            canonical_json_value(asdict(result)),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


async def _run() -> int:
    args = _parser().parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    config = load_parameter_inference_config(Path(args.config))
    payload: dict[str, object] = {
        "location": _build_location(args),
        "varieties": _parse_variety_area(args.variety_area),
    }
    if args.as_of_date is not None:
        payload["as_of_date"] = args.as_of_date

    async with AsyncSessionMaker() as session:
        result = await create_minimal_planning_task(
            session,
            payload=payload,
            config=config,
            dry_run=args.dry_run,
            library_version_code=args.library_version,
        )

    _write_result(Path(args.output), result)
    logging.info(
        "status=%s task_id=%s run_id=%s input_hash=%s",
        result.status,
        result.task_id,
        result.run_id,
        result.input_hash,
    )
    await dispose_db_engine()
    return 1 if result.status == "failed" else 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
