"""Public synthetic engineering closeout replay, not historical model reproduction."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from backend.app.area_yield import m0_baseline
from backend.app.area_yield import research_records_r2 as rr
from backend.app.area_yield.base_product import AreaForecastProductRequest
from backend.app.area_yield.data import calendar, digest

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = "docs/v0-11/evidence/v0.11.0-research-engineering-closeout.json"
PUBLIC = "artifacts/v0-11-closeout"


def require(value: bool, code: str) -> None:
    if not value:
        raise ValueError(code)


def verify_boundary(payload: dict[str, Any]) -> None:
    require(
        payload["VERSION"] == "0.11.0"
        and payload["V0_11_LIFECYCLE"] == "CLOSED_ENGINEERING_DELIVERED_NOT_ISSUED"
        and payload["REFERENCE_BASELINE_ID"] == m0_baseline.MODEL_ID
        and payload["REFERENCE_BASELINE_FAMILY"] == m0_baseline.MODEL_FAMILY
        and payload["REFERENCE_BASELINE_ROLE"] == "REFERENCE_BASELINE"
        and payload["REFERENCE_BASELINE_APPROVAL"] == "RESEARCH_ONLY"
        and payload["CONDITIONAL_MODEL_ROLE"] == "DIAGNOSTIC_ONLY"
        and payload["REAL_FORECAST_COUNT"] == 0,
        "CLOSEOUT_IDENTITY",
    )
    for key in (
        "VERSION_COMPLETE",
        "REAL_PROSPECTIVE_ISSUANCE_EXECUTED",
        "REAL_PROSPECTIVE_SCORING_EXECUTED",
        "PROSPECTIVE_ACCURACY_VALIDATED",
        "PROBABILITY_CALIBRATION_ESTABLISHED",
        "PRODUCTION_USE_APPROVED",
        "PRODUCTION_ACCURACY_VALIDATED",
        "BUSINESS_ACCURACY_THRESHOLD_ESTABLISHED",
        "CONDITIONAL_MODELS_PROMOTED",
        "V0_11_REOPEN_FOR_FUTURE_REQUEST",
        "MODEL_TRAINING_ON_PRIVATE_REAL_DATA",
        "NEW_MODEL_SEARCH_EXECUTED",
        "NEW_BACKTEST_EXECUTED",
        "READY_AUTHORIZED",
        "MERGE_AUTHORIZED",
        "TAG_CREATED",
        "GITHUB_RELEASE_CREATED",
    ):
        require(payload[key] is False, "CLOSEOUT_GATE:" + key)
    for key in (
        "V0_11_LIFECYCLE_CLOSED",
        "ENGINEERING_SCOPE_DELIVERED",
        "TRAIN_SAVE_LOAD_PREDICT_DELIVERED",
        "FILE_MODE_ISSUANCE_DELIVERED",
        "ACTUAL_SNAPSHOT_DELIVERED",
        "LOCKED_SCORING_DELIVERED",
        "NO_FURTHER_V0_11_MODEL_SEARCH",
        "HISTORICAL_RESULTS_ARE_NOT_NEW_VALIDATION",
    ):
        require(payload[key] is True, "CLOSEOUT_DELIVERY:" + key)
    require(
        "CURRENT_CHAMPION" not in payload and "CHAMPION_CHANGED" not in payload,
        "CLOSEOUT_NO_PROMOTION_IDENTITY",
    )


def write(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    return path


def cli(*args: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "backend.app.cli", "m0-baseline", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    payload: dict[str, Any] = json.loads(result.stdout)
    return payload


def synthetic_replay(root: Path) -> dict[str, Any]:
    days = [date(2023, 7, 1) + timedelta(days=i) for i in range(14)]
    training = write(
        root / "training.json",
        [
            {
                "base_id": "base_" + "a" * 24,
                "group_id": "SYNTHETIC|2023-2024",
                "season": "2023-2024",
                "area": 10.0,
                "dates": [d.isoformat() for d in days],
                "quantities": [float(i + 1) for i in range(14)],
                "total": 105.0,
            }
        ],
    )
    manifest = write(
        root / "training-manifest.json",
        {
            "training_input_sha256": rr.file_hash(training),
            "base_season_count": 1,
            "scope": "SYNTHETIC_TEST_ONLY",
        },
    )
    model_path = root / "model.json"
    cli(
        "train",
        "--training-input",
        str(training),
        "--manifest",
        str(manifest),
        "--output",
        str(model_path),
    )
    model = m0_baseline.load_model(model_path)
    request = {
        "base_id": "base_" + "a" * 24,
        "target_area_mu": "10",
        "target_season": "2027-2028",
        "forecast_start_date": "2027-07-01",
        "forecast_end_date": "2028-04-15",
        "forecast_mode": "EXPERIMENTAL",
    }
    request_path = write(root / "request.json", request)
    predictions = []
    for i in range(2):
        path = root / f"response-{i}.json"
        cli(
            "predict",
            "--model",
            str(model_path),
            "--input",
            str(request_path),
            "--output",
            str(path),
        )
        predictions.append(path.read_bytes())
    require(predictions[0] == predictions[1], "DETERMINISTIC_INFERENCE")
    registry = write(
        root / "registry.json",
        {
            "default_research_model_id": m0_baseline.MODEL_ID,
            "models": [
                {
                    "model_id": m0_baseline.MODEL_ID,
                    "model_family": m0_baseline.MODEL_FAMILY,
                    "model_role": "REFERENCE_BASELINE",
                    "approval_status": "RESEARCH_ONLY",
                    "artifact_file_sha256": rr.file_hash(model_path),
                    "artifact_hash": model["artifact_hash"],
                    "training_manifest_sha256": model["training_manifest_sha256"],
                    "training_cutoff": model["training_cutoff"],
                    "supported_request_window": "JULY_01_THROUGH_APRIL_15_INCLUSIVE",
                }
            ],
        },
    )
    snapshot = AreaForecastProductRequest.model_validate(request).model_dump(mode="json")
    local = {
        "status": "TEST_ONLY",
        "operator": "SYNTHETIC_TEST_OPERATOR",
        "request_snapshot_hash": digest(snapshot),
        "target_actuals_used": False,
        "revision_reason": None,
    }
    raw = write(root / "authorization-source.json", local)
    authorization = write(
        root / "authorization.json",
        {
            "local_record": local,
            "source": {
                "source_id": "SYNTHETIC_AUTH",
                "source_version": "1",
                "raw_source_hash": rr.file_hash(raw),
                "canonical_payload_hash": digest(local),
                "normalization_version": "EXACT_REQUEST_AUTH_R2",
                "raw_source_path": str(raw),
            },
        },
    )
    store = root / "store"
    seal_id = cli(
        "issue",
        "--store",
        str(store),
        "--registry",
        str(registry),
        "--registry-sha256",
        rr.file_hash(registry),
        "--model",
        str(model_path),
        "--model-id",
        m0_baseline.MODEL_ID,
        "--input",
        str(request_path),
        "--authorization",
        str(authorization),
        "--test-clock",
        "2027-06-01T00:00:00+00:00",
    )["id"]
    cli("verify-seal", "--store", str(store), "--model", str(model_path), "--seal-id", seal_id)
    rows = [
        {
            "date": d.isoformat(),
            "status": "OBSERVED",
            "new_quantity_kg": "1.000000",
        }
        for d in calendar(date(2027, 7, 1), date(2028, 4, 15))
    ]
    actual_raw = write(root / "actual-source.json", rows)
    actual = write(
        root / "actual-input.json",
        {
            "base_id": request["base_id"],
            "target_season": request["target_season"],
            "unit": "kg",
            "rows": rows,
            "supersedes": None,
            "revision_reason": None,
            "source_identity": {
                "source_id": "SYNTHETIC_ACTUAL",
                "source_version": "1",
                "raw_source_hash": rr.file_hash(actual_raw),
                "canonical_payload_hash": digest(rows),
                "normalization_version": "IDENTITY_JSON_MICROKG_R2",
                "raw_source_path": str(actual_raw),
            },
        },
    )
    actual_id = cli(
        "import-actuals",
        "--store",
        str(store),
        "--seal-id",
        seal_id,
        "--input",
        str(actual),
        "--test-clock",
        "2028-04-16T00:00:00+00:00",
    )["id"]
    common = [
        "evaluate",
        "--store",
        str(store),
        "--model",
        str(model_path),
        "--seal-id",
        seal_id,
        "--actual-id",
        actual_id,
        "--metric-contract",
        rr.CONTRACT,
        "--test-clock",
        "2028-04-17T00:00:00+00:00",
    ]
    first = cli(*common)
    before = {p: p.read_bytes() for p in store.glob("*/*/record.json")}
    second = cli(*common)
    first_metrics = rr.read(Path(first["record_path"]))["metrics"]
    require(first_metrics == rr.read(Path(second["record_path"]))["metrics"], "LOCKED_METRICS")
    require(all(p.read_bytes() == value for p, value in before.items()), "IMMUTABLE_RECORDS")
    require(
        rr.read(store / "predictions" / seal_id / "record.json")["test_only"], "TEST_ONLY_REQUIRED"
    )
    return {
        "cli_commands": ["train", "predict", "issue", "verify-seal", "import-actuals", "evaluate"],
        "prediction_hash": hashlib.sha256(predictions[0]).hexdigest(),
        "metrics_hash": digest(first_metrics),
        "mode": "TEST_NOT_PROSPECTIVE",
    }


def replay() -> dict[str, Any]:
    verify_boundary(rr.read(ROOT / BOUNDARY))
    manifest = rr.read(ROOT / PUBLIC / "public-artifact-manifest.json")
    for item in manifest["files"]:
        relative = Path(item["path"])
        require(not relative.is_absolute() and ".." not in relative.parts, "PUBLIC_PATH")
        require(rr.file_hash(ROOT / relative) == item["sha256"], "PUBLIC_HASH:" + str(relative))
    extraction = rr.read(ROOT / PUBLIC / "extraction-manifest.json")
    require(len(extraction["files"]) == 22, "EXTRACTION_SOURCE_COUNT")
    for item in extraction["files"]:
        if item["destination"] is None:
            require(
                item["classification"] == "NOT_REQUIRED_FOR_V0_11_CLOSEOUT", "EXTRACTION_EXCLUDED"
            )
    for item in extraction["protected_v0_10_files"]:
        require(rr.file_hash(ROOT / item["path"]) == item["sha256"], "V0_10_IMMUTABLE")
    with tempfile.TemporaryDirectory(prefix="v011-closeout-test-only-") as directory:
        result = synthetic_replay(Path(directory))
    return {
        "status": "PASS",
        "level": "ENGINEERING_CLOSEOUT_REPLAY",
        "private_row_level_data_required": False,
        "real_forecast_count": 0,
        "historical_training_reproduced": False,
        "new_backtest_executed": False,
        "synthetic_replay": result,
    }


if __name__ == "__main__":
    print(json.dumps(replay(), sort_keys=True))
