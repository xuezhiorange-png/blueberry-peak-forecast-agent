"""Explicit-path local E2 verification, never opening historical source data.

Creates new controlled TEST_ONLY outputs; original artifacts stay read-only.
No actual import/scoring, no model training and no artifact serialization.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from backend.app.area_yield import artifact_registration as e2
from backend.app.area_yield import prospective_validation as e1
from backend.app.area_yield.data import digest
from backend.app.area_yield.research_records import file_hash, read
from backend.app.area_yield.research_records_r2 import _write


def run(
    candidate: Path,
    baseline: Path,
    receipt_path: Path,
    seal_path: Path,
    contract_path: Path,
    public_path: Path,
    output: Path,
) -> dict[str, Any]:
    public = read(public_path)
    before = [(file_hash(p), p.stat().st_size, p.stat().st_mtime_ns) for p in (candidate, baseline)]
    # Read only the explicitly authorized delivery metadata, never resolve source hashes.
    receipt, seal, contract = map(read, (receipt_path, seal_path, contract_path))
    expected = public["fold"]
    for key in (
        "artifact_file_hashes",
        "train_seasons",
        "test_season",
        "train_sample_count",
        "test_sample_count",
        "created_at",
    ):
        if seal[key] != expected[key] or receipt["fold"][key] != expected[key]:
            raise ValueError("DELIVERY_SEAL_PROVENANCE_MISMATCH")
    for key, value in {
        "fresh_process": "PASS",
        "deterministic_training": "PASS",
        "scientific_result": "RESEARCH_CANDIDATE_NO_STABLE_GAIN",
        "stable_gain": False,
        "training_area_range": ["216", "2548"],
    }.items():
        if receipt[key] != value:
            raise ValueError("DELIVERY_RECEIPT_PROVENANCE_MISMATCH")
    c = read(candidate)
    frozen_config = (
        Path(__file__).resolve().parents[1] / "configs/next_area_size_experiment_20261002_r1.json"
    )
    if (
        contract["execution_id"] != e2.EXECUTION
        or contract["train_seasons"] != ["2023-2024"]
        or contract["test_season"] != "2024-2025"
        or contract["candidate_penalty"] != 1.0
        or contract["search"] is not False
        or contract["holdout_refitted_into_final_artifact"] is not False
        or file_hash(frozen_config) != c["training_identity"]["configuration_hash"]
        or read(frozen_config) != contract
    ):
        raise ValueError("DELIVERY_EXECUTION_CONTRACT_MISMATCH")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    commands: list[dict[str, Any]] = []
    guard = (
        "from backend.app.area_yield import area_size_r1; "
        "exec('def reject_fit(*args, **kwargs):\\n "
        'raise RuntimeError("MODEL_TRAINING_FORBIDDEN")\'); '
        "area_size_r1.fit = reject_fit; "
        "from backend.app.area_yield.prospective_validation_cli import main; main()"
    )

    def call(*args: str) -> dict[str, Any]:
        command = [sys.executable, "-c", guard, "v0-12-research", *args]
        r = subprocess.run(command, check=True, capture_output=True, text=True)
        commands.append(
            {"operation": args[0], "exit_code": r.returncode, "fit_guard_enabled": True}
        )
        result: dict[str, Any] = json.loads(r.stdout)
        return result

    registry = output / "runtime-verified-registry.json"
    verification = call(
        "register-artifacts",
        "--candidate",
        str(candidate),
        "--baseline",
        str(baseline),
        "--public-evidence",
        str(public_path),
        "--output",
        str(registry),
    )
    # Independent process plus original fixed public example; guard is enabled before inference.
    predictions = []
    for artifact in (candidate, baseline):
        results = []
        for _ in range(2):
            r = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from backend.app.area_yield.artifact_registration import guarded_predict; "
                    "from pathlib import Path; import json,sys; "
                    "print(json.dumps(guarded_predict(Path(sys.argv[1])),sort_keys=True))",
                    str(artifact),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            results.append(json.loads(r.stdout))
        if results[0] != results[1]:
            raise ValueError("FRESH_PROCESS_REPLAY_MISMATCH")
        predictions.append(results[0])
    example = public["example"]
    for key in ("predicted_season_total_kg", "peaks", "result_hash", "model_id", "artifact_hash"):
        if predictions[0][key] != example[key]:
            raise ValueError("PUBLIC_EXAMPLE_PARITY_MISMATCH")
    entries = read(registry)["entries"]
    request = {
        "request_id": "E2_TEST_ONLY_ORIGINAL_ARTIFACT",
        "request_mode": "TEST_ONLY",
        "requested_at": "2026-06-01T00:00:00+08:00",
        "target_area_mu": "736.000000",
        "target_season": "2026-2027",
        "base_id_or_farm_context": "TEST_ONLY_UNSEEN_BASE",
        "forecast_start_date": "2026-07-01",
        "forecast_end_date": "2027-04-15",
        "candidate_model_id": entries[0]["registry_id"],
        "candidate_artifact_hash": entries[0]["artifact_hash"],
        "candidate_config_hash": entries[0]["config_hash"],
        "comparator_id": entries[1]["registry_id"],
        "comparator_artifact_or_policy_hash": entries[1]["artifact_hash"],
        "request_source_id": "E2_SYNTHETIC_SOURCE",
        "request_source_version": "1",
        "request_source_hash": "0" * 64,
        "authorization_id": "E2_TEST_ONLY_AUTH",
        "authorization_status": "TEST_ONLY",
    }
    source = output / "TEST_ONLY-source.json"
    _write(source, e1.request_source_payload(request))
    request["request_source_hash"] = file_hash(source)
    request_path = output / "TEST_ONLY-request.json"
    _write(request_path, request)
    authorization = output / "TEST_ONLY-authorization.json"
    _write(
        authorization,
        {
            "authorization_id": request["authorization_id"],
            "status": "TEST_ONLY",
            "request_hash": digest(request),
            "operator": "E2_CONTROLLED_TEST_OPERATOR",
        },
    )
    store = output / "TEST_ONLY-records"
    issue_args = [
        "--store",
        str(store),
        "--registry",
        str(registry),
        "--registry-hash",
        file_hash(registry),
        "--input",
        str(request_path),
        "--source",
        str(source),
        "--authorization",
        str(authorization),
        "--test-clock",
        "2026-06-02T00:00:00+08:00",
    ]
    forecast = call("issue", *issue_args)["record"]
    call("verify-seal", "--store", str(store), "--forecast-id", forecast["id"])
    if forecast["prediction"]["candidate"]["result_hash"] != example["result_hash"]:
        raise ValueError("ISSUED_EXAMPLE_PARITY_MISMATCH")
    request["request_mode"] = "REAL_PROSPECTIVE"
    rejected = output / "REAL_REJECT_TEST-request.json"
    _write(rejected, request)
    real_args = list(issue_args)
    real_args[real_args.index(str(request_path))] = str(rejected)
    r = subprocess.run(
        [sys.executable, "-c", guard, "v0-12-research", "issue", *real_args],
        capture_output=True,
        text=True,
    )
    if r.returncode != 2 or "REAL_PROSPECTIVE_NOT_AUTHORIZED" not in r.stderr:
        raise ValueError("REAL_MODE_NOT_REJECTED")
    after = [(file_hash(p), p.stat().st_size, p.stat().st_mtime_ns) for p in (candidate, baseline)]
    if before != after:
        raise ValueError("ORIGINAL_ARTIFACT_MUTATED")
    evidence = {
        **verification,
        "fresh_process_load_predict": "PASS",
        "public_example_parity": "PASS",
        "deterministic_inference_replay": "PASS",
        "verified_artifact_test_only_issuance": "PASS",
        "real_prospective_rejection": "PASS",
        "real_forecast_count": 0,
        "real_prospective_enabled": False,
        "scientific_score_role": "NONE",
        "model_retrained": False,
        "new_backtest": False,
        "raw_training_data_read": False,
        "private_row_level_data_read": False,
        "artifact_stat_before_after_parity": True,
        "test_forecast_id": forecast["id"],
        "commands": commands,
        "candidate_inference_hash": predictions[0]["result_hash"],
        "comparator_inference_hash": predictions[1]["result_hash"],
    }
    _write(output / "local-verification-result.json", evidence)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in (
        "candidate",
        "baseline",
        "receipt",
        "seal",
        "execution-contract",
        "public-evidence",
        "output-dir",
    ):
        parser.add_argument(f"--{arg}", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.candidate,
                args.baseline,
                args.receipt,
                args.seal,
                args.execution_contract,
                args.public_evidence,
                args.output_dir,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
