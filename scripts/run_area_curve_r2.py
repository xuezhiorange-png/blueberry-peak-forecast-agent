"""Isolated R2 commands. R1 files are read-only; no raw XLS, DB or legacy TEST loader."""

import argparse
import json
import subprocess
from pathlib import Path

from backend.app.area_yield import single_season_r2 as application
from backend.app.area_yield.experiment import read_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("rolling", "benchmark", "refit", "forecast"))
    parser.add_argument("--r1", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/area_yield_experiment_r2.json")
    )
    args = parser.parse_args()
    if args.phase == "rolling":
        result = application.rolling(
            args.output,
            args.r1,
            read_json(args.config),
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        )
    elif args.phase == "benchmark":
        result = application.benchmark(args.output, args.r1)
    elif args.phase == "refit":
        result = application.refit(args.output, args.r1)
    else:
        result = application.forecast(args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
