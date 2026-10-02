"""Thin R2 research resource in the existing application CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from backend.app.area_yield import conditional_growth_r2 as core
from backend.app.area_yield.base_product import AreaForecastProductRequest
from backend.app.core_forecast.cli import CoreForecastCliError


def register_r2(parsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    actions = parsers.add_parser("conditional-growth-r2").add_subparsers(
        dest="command", required=True
    )
    train = actions.add_parser("train")
    for name in ("input", "config", "output"):
        train.add_argument("--" + name, required=True)
    predict = actions.add_parser("predict")
    for name in ("model", "input", "output"):
        predict.add_argument("--" + name, required=True)


def dispatch_r2(args: argparse.Namespace, stdout: TextIO) -> None:
    output: Any
    try:
        if args.command == "train":
            data, config = (json.loads(Path(p).read_text()) for p in (args.input, args.config))
            output, _, _ = core.fit_model(
                data["fit_targets"],
                data["historical_context"],
                data["weather_reference"],
                data["mix"],
                config["shape"],
                config["total"],
                config["m0_density"],
                config["contract_hash"],
                config["role"],
            )
        else:
            allowed = {Path(args.model).resolve(), Path(args.input).resolve()}

            def guard(event: str, values: tuple[Any, ...]) -> None:
                if event == "open" and isinstance(values[0], str):
                    path = Path(values[0]).resolve()
                    if isinstance(values[1], str) and any(k in values[1] for k in "wax"):
                        return
                    if path not in allowed and path.suffix in {".csv", ".jsonl", ".xlsx", ".xls"}:
                        raise PermissionError("R2_INFERENCE_FORBIDDEN_DATA_READ")

            sys.addaudithook(guard)
            model, raw = (json.loads(Path(p).read_text()) for p in (args.model, args.input))
            requests = raw if isinstance(raw, list) else [raw]
            values = [
                core.forecast(
                    model, AreaForecastProductRequest.model_validate(r).model_dump(mode="json")
                )
                for r in requests
            ]
            output = values if isinstance(raw, list) else values[0]
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as stream:
            json.dump(output, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
        stdout.write(json.dumps({"status": "R2_RESEARCH_ONLY", "action": args.command}) + "\n")
    except (ValueError, KeyError, OSError, TypeError) as error:
        raise CoreForecastCliError("CONDITIONAL_R2_ERROR", str(error), exit_code=2) from error
