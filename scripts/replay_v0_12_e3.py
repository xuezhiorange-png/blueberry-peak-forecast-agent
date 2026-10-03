"""Non-destructive E3 drill from a bundle only, never from original source paths.

Uses E2's guarded fresh-process verification and E1 TEST_ONLY issue/seal.
No actual/scientific scoring, training or historical data read.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.app.area_yield import recovery_bundle as e3
from backend.app.area_yield.research_records_r2 import _write
from scripts.verify_v0_12_e2 import run as verify_restored


def run(bundle: Path, restored: Path, test_output: Path, audit_output: Path) -> dict[str, Any]:
    custody = e3.restore(bundle, restored)
    replay = verify_restored(
        restored / e3.CANDIDATE,
        restored / e3.BASELINE,
        restored / e3.RECEIPT,
        restored / e3.SEAL,
        restored / e3.CONTRACT,
        restored / e3.PUBLIC,
        test_output,
    )
    registry = test_output / "runtime-verified-registry.json"
    store = test_output / "TEST_ONLY-records"
    drill = e3.drill_result(restored, registry, store, replay["test_forecast_id"])
    result_path = test_output / "restore-drill-result.json"
    _write(result_path, drill)
    audit = e3.audit_export(bundle, restored, registry, result_path, store, audit_output)
    result = {
        **custody,
        "disaster_recovery_drill": "PASS",
        "restored_runtime_registry_verified": True,
        "restored_public_example_parity": replay["public_example_parity"],
        "restored_test_only_issuance": replay["verified_artifact_test_only_issuance"],
        "fresh_process_load_predict": replay["fresh_process_load_predict"],
        "real_prospective_rejection": replay["real_prospective_rejection"],
        "audit_export_sanitized": audit["audit_export_sanitized"],
        "audit_hash": audit["audit_hash"],
        "forecast_id": replay["test_forecast_id"],
        "candidate_prediction_hash": replay["candidate_inference_hash"],
        "real_forecast_count": 0,
        "model_retrained": False,
        "raw_training_data_read": False,
        "private_row_level_data_read": False,
        "scientific_score_role": "NONE",
    }
    _write(test_output / "e3-replay-result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("bundle", "restore-root", "test-output", "audit-output"):
        parser.add_argument(f"--{arg}", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.bundle, args.restore_root, args.test_output, args.audit_output), indent=2
        )
    )


if __name__ == "__main__":
    main()
