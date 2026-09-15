"""Create a deterministic, aggregate R3 authority-rebind replay report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.audit_v0_5_s3_training_eligibility_r1 import file_hash
from scripts.report_v0_5_s3_training_eligibility_r1 import compare


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(first: Path, second: Path) -> dict[str, Any]:
    replay = compare(first, second)
    first_rebind = read_json(first / "r3-authority-rebind.json")
    first_scope = read_json(first / "r3-scope-reconciliation.json")
    read_json(first / "summary.json")
    return {
        "task_id": "V0_5_S3_ELIGIBILITY_AUTHORITY_REBIND_R3",
        "result": "S3_ELIGIBILITY_AUTHORITY_REBOUND",
        "authority_rebind": first_rebind,
        "scope_reconciliation": first_scope["scope"],
        "support_counts_by_season": first_scope["support_counts_by_season"],
        "forward_folds": first_scope["forward_folds"],
        "full_season_status": first_scope["full_season_status"],
        "full_season_model_authorized": False,
        "summary_hash": file_hash(first / "summary.json"),
        "replay": replay,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Read the summary explicitly so a malformed/missing summary cannot be
    # hidden behind the replay comparison's aggregate checks.
    read_json(args.first / "summary.json")
    report = build_report(args.first, args.second)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    args.output.chmod(0o600)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
