"""Research adapter inside the existing application CLI, never production default."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from backend.app.area_yield import conditional_growth as cg
from backend.app.area_yield.base_product import AreaForecastProductRequest
from backend.app.core_forecast.cli import CoreForecastCliError


def register_conditional_parser(
    parsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    resource = parsers.add_parser("conditional-growth")
    actions = resource.add_subparsers(dest="command", required=True)
    train = actions.add_parser("train")
    train.add_argument("--input", required=True)
    train.add_argument("--config", required=True)
    train.add_argument("--output", required=True)
    predict = actions.add_parser("predict")
    predict.add_argument("--model", required=True)
    predict.add_argument("--input", required=True)
    predict.add_argument("--output", required=True)


def dispatch_conditional(args: argparse.Namespace, stdout: TextIO) -> None:
    output: Any
    try:
        if args.command == "train":
            data = json.loads(Path(args.input).read_text())
            config = json.loads(Path(args.config).read_text())
            output, _, _ = cg.fit_model(
                data["samples"],
                data["weather"],
                data["mix"],
                config["shape"],
                config["total"],
                config["m0_density"],
                config["contract_hash"],
                config["role"],
            )
        else:
            allowed = {Path(args.model).resolve(), Path(args.input).resolve()}
            protected = Path(__file__).resolve().parents[3] / "artifacts"

            def audit(event: str, values: tuple[Any, ...]) -> None:
                if event != "open" or not isinstance(values[0], (str, bytes)):
                    return
                path = Path(
                    values[0].decode() if isinstance(values[0], bytes) else values[0]
                ).resolve()
                if isinstance(values[1], str) and any(k in values[1] for k in ("w", "a", "x")):
                    return
                if path not in allowed and (
                    path.suffix in {".csv", ".jsonl", ".xlsx", ".xls"}
                    or path.is_relative_to(protected)
                ):
                    raise PermissionError("CONDITIONAL_INFERENCE_FORBIDDEN_DATA_READ")

            sys.addaudithook(audit)
            model = json.loads(Path(args.model).read_text())
            raw = json.loads(Path(args.input).read_text())
            requests = raw if isinstance(raw, list) else [raw]
            predictions = []
            for r in requests:
                request = AreaForecastProductRequest.model_validate(r).model_dump(mode="json")
                if request["base_id"] is None:
                    raise ValueError("ANONYMOUS_BASE_ID_REQUIRED_FOR_HISTORY_RETRIEVAL")
                predictions.append(cg.forecast(model, request))
            output = predictions if isinstance(raw, list) else predictions[0]
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as stream:
            json.dump(output, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
        stdout.write(
            json.dumps(
                {
                    "status": "RESEARCH_ONLY_COMPLETED",
                    "action": args.command,
                    "inference_data_guard": args.command == "predict",
                }
            )
            + "\n"
        )
    except (ValueError, OSError, TypeError, KeyError) as error:
        raise CoreForecastCliError("CONDITIONAL_GROWTH_ERROR", str(error), exit_code=2) from error
