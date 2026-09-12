"""Run with python -m scripts.run_area_yield_experiment; no DB/legacy TEST access."""

import argparse
import json
import subprocess
from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.app.area_yield.data import Receipt
from backend.app.area_yield.experiment import final_evaluate, forecast, prepare, read_json, train


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "train", "final", "predict"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/area_yield_experiment_r1.json")
    )
    parser.add_argument("--area", type=Decimal)
    parser.add_argument("--season-start-year", type=int)
    parser.add_argument("--cutoff", type=date.fromisoformat)
    parser.add_argument("--scope")
    args = parser.parse_args()
    if args.phase == "prepare":
        # Lazy import: predict/train/final do not even import a historical XLS loader.
        from scripts.probe_banna_harvest_baseline_r4 import SOURCE, SOURCE_HASH, load_verified_facts

        config = read_json(args.config)
        if str(SOURCE) != config["source_path"] or SOURCE_HASH != config["source_hash"]:
            raise ValueError("only pinned pre-legacy-TEST source authorized")
        if (
            config["scope_id"] != "BANNA_MENGWANG_DX_736MU_R1"
            or config["area_mu"] != "736.000000"
            or config["area_basis"] != "AUTHORIZED_CALIBRATION"
            or config["coverage_start"] != "2024-10-15"
            or config["coverage_end"] != "2025-05-09"
        ):
            raise ValueError("pinned source cannot be relabeled or assigned another denominator")
        facts = load_verified_facts()
        receipts = [
            Receipt(
                f.source_row_identity,
                config["scope_id"],
                config["season_id"],
                f.harvest_date,
                f.arrival_quantity_kg,
                "DETAIL",
            )
            for f in facts
        ]
        result = prepare(
            args.output,
            config,
            receipts,
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        )
    elif args.phase == "train":
        result = train(args.output)
    elif args.phase == "final":
        result = final_evaluate(args.output)
    else:
        if any(v is None for v in (args.area, args.season_start_year, args.cutoff, args.scope)):
            parser.error("predict requires --area --season-start-year --cutoff --scope")
        result = forecast(args.output, args.area, args.season_start_year, args.cutoff, args.scope)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
