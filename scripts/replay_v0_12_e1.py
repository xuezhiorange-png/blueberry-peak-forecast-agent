"""Public TEST_ONLY E1 replay via fresh instances of the existing app CLI.

python -m scripts.replay_v0_12_e1 --output-dir <new-directory>
Never imports training or private data and never performs scientific evaluation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from backend.app.area_yield import prospective_validation as e1
from backend.app.area_yield.research_records import file_hash
from backend.app.area_yield.research_records_r2 import _write
from backend.app.area_yield.v0_12_e1_fixtures import bind_actual, make_fixture


def replay(root: Path) -> dict[str, Any]:
    case = make_fixture(root)
    commands = []

    def call(name: str, *arguments: Any, store: Path | None = None) -> dict[str, Any]:
        command = [
            sys.executable,
            "-m",
            "backend.app.area_yield.prospective_validation_cli",
            "v0-12-research",
            name,
            "--store",
            str(store or case["store"]),
            *map(str, arguments),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        commands.append({"command": command, "exit_code": result.returncode})
        record: dict[str, Any] = json.loads(result.stdout)["record"]
        return record

    issue_arguments = [
        "--registry",
        case["registry"],
        "--registry-hash",
        file_hash(case["registry"]),
        "--input",
        root / "example-request.json",
        "--source",
        case["source"],
        "--authorization",
        case["authorization"],
        "--test-clock",
        case["issue_clock"].isoformat(),
    ]
    forecast = call("issue", *issue_arguments)
    verified = call("verify-seal", "--forecast-id", forecast["id"])
    bind_actual(case, forecast["id"])
    revision = call(
        "import-actuals",
        "--forecast-id",
        forecast["id"],
        "--input",
        root / "example-actual.json",
        "--source",
        case["actual_source"],
        "--test-clock",
        case["actual_clock"].isoformat(),
    )
    snapshot = call(
        "create-snapshot",
        "--forecast-id",
        forecast["id"],
        "--revision-id",
        revision["id"],
        "--test-clock",
        case["actual_clock"].isoformat(),
    )
    evaluation_arguments = [
        "--forecast-id",
        forecast["id"],
        "--snapshot-id",
        snapshot["id"],
        "--metric-contract",
        e1.CONTRACT,
        "--test-clock",
        case["actual_clock"].isoformat(),
    ]
    evaluation = call("evaluate", *evaluation_arguments)
    second_evaluation = call("evaluate", *evaluation_arguments)
    repeated = call("issue", *issue_arguments, store=root / "replay-records")
    if not (
        forecast["prediction_hash"] == verified["prediction_hash"] == repeated["prediction_hash"]
        and evaluation["metrics_hash"] == second_evaluation["metrics_hash"]
    ):
        raise ValueError("ENGINEERING_REPLAY_PARITY_FAILED")
    summary = {
        "scope": "V0_12_E1_ENGINEERING_READINESS_REPLAY",
        "test_only": True,
        "test_not_prospective": True,
        "synthetic_artifact_not_trained": True,
        "forecast_id": forecast["id"],
        "actual_snapshot_id": snapshot["id"],
        "evaluation_id": evaluation["id"],
        "prediction_hash": forecast["prediction_hash"],
        "metrics_hash": evaluation["metrics_hash"],
        "deterministic_replay": "PASS",
        "fresh_process_cli": "PASS",
        "commands": commands,
        "stable_gain_decision": "NOT_EXECUTED",
        "real_forecast_count": 0,
        "model_retrained": False,
        "new_backtest": False,
        "private_data_read": False,
        "metrics": evaluation["metrics"],
        "hash_scope": (
            "Prediction and metrics numeric content, not random run IDs or issuance timestamps"
        ),
    }
    _write(root / "replay-result.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.output_dir)
    print(
        json.dumps({k: v for k, v in result.items() if k not in {"metrics", "commands"}}, indent=2)
    )


if __name__ == "__main__":
    main()
